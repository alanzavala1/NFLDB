import type { PlayerChart } from '../../types'
import { zoneShade } from './playerChartStats'

const GAP_ORDER = [
  { key: 'left end', label: 'L END' },
  { key: 'left tackle', label: 'L TKL' },
  { key: 'left guard', label: 'L GRD' },
  { key: 'middle', label: 'MID' },
  { key: 'right guard', label: 'R GRD' },
  { key: 'right tackle', label: 'R TKL' },
  { key: 'right end', label: 'R END' },
] as const

const GAP_X: Record<string, number> = {
  'left end': 9, 'left tackle': 22.6, 'left guard': 36.3, middle: 50,
  'right guard': 63.6, 'right tackle': 77.3, 'right end': 91,
}

const RUN_H = 200

function runDepth(yards: number) {
  return 34 + Math.min(27, Math.max(-3, yards)) * 5
}

export function RunMap({ events }: { events: PlayerChart['events'] }) {
  const lanes = new Map<string, { yards: number; outcome: string }[]>()
  for (const e of events) {
    if (e.role !== 'rusher') continue
    const gap = (e.lane ?? '').toLowerCase().trim()
    if (!(gap in GAP_X)) continue
    lanes.set(gap, [...(lanes.get(gap) ?? []), { yards: Number(e.yards ?? 0), outcome: e.outcome }])
  }
  if (![...lanes.values()].some(l => l.length)) return null
  const dots: { x: number; b: number; yards: number; outcome: string }[] = []
  for (const [gap, list] of lanes) {
    list.sort((a, b) => a.yards - b.yards)
    list.forEach((e, i) => dots.push({ x: GAP_X[gap] + [0, -4, 4, -2, 2][i % 5], b: runDepth(e.yards), yards: e.yards, outcome: e.outcome }))
  }
  return (
    <div>
      <div className="micro">Carry map</div>
      <div className="tmap rmap" style={{ height: RUN_H }}>
        {[10, 20].map(d => <span key={d} className="tm-yard" style={{ bottom: runDepth(d) }} />)}
        {[10, 20].map(d => <span key={d} className="tm-depth" style={{ bottom: runDepth(d) - 5 }}>{d}</span>)}
        <div className="tm-los" style={{ bottom: runDepth(0) }} />
        <span className="tm-los-label" style={{ bottom: runDepth(0) - 14 }}>LOS</span>
        {[22.6, 36.3, 50, 63.6, 77.3].map(x => <span key={x} className="rm-oc" style={{ left: `${x}%`, bottom: runDepth(0) - 6 }} />)}
        {Object.entries(GAP_X).map(([gap, x]) => <span key={gap} className="rm-gap" style={{ left: `${x}%` }}>{GAP_ORDER.find(g => g.key === gap)?.label}</span>)}
        {dots.map((d, i) => {
          const cls = d.outcome === 'TD' ? 'td' : d.yards <= 0 ? 'int' : 'catch'
          return <span key={i} className={`tm-dot ${cls}`} style={{ left: `${d.x}%`, bottom: d.b }}>{d.outcome === 'TD' ? '✦' : ''}</span>
        })}
      </div>
      <div className="legend">
        <span className="lg"><i className="tm-key catch" />Gain</span>
        <span className="lg"><i className="tm-key" style={{ background: 'var(--rate-bad)' }} />Stuffed</span>
        <span className="lg" style={{ color: 'var(--rate-good)' }}>✦ TD</span>
      </div>
    </div>
  )
}

export function GapStrip({ events }: { events: PlayerChart['events'] }) {
  const gaps = new Map<string, { att: number; yds: number; td: boolean }>()
  for (const e of events) {
    if (e.role !== 'rusher') continue
    const key = (e.lane ?? '').toLowerCase().trim()
    if (!GAP_ORDER.some(g => g.key === key)) continue
    const cell = gaps.get(key) ?? { att: 0, yds: 0, td: false }
    cell.att += 1
    cell.yds += Number(e.yards ?? 0)
    if (e.outcome === 'TD') cell.td = true
    gaps.set(key, cell)
  }
  if (gaps.size === 0) return null
  return (
    <div className="zones-wrap">
      <div className="micro">By gap · carries &amp; yards</div>
      <div className="gaps">
        {GAP_ORDER.map(g => {
          const cell = gaps.get(g.key)
          return <div key={g.key} className={`gcell ${zoneShade(cell?.att ?? 0)}`}>
            {cell?.td && <span className="zstar">✦</span>}
            <b>{cell?.att ?? '—'}</b>
            {cell && <small>{Math.round(cell.yds)} yds</small>}
            <span className="glab">{g.label}</span>
          </div>
        })}
      </div>
    </div>
  )
}
