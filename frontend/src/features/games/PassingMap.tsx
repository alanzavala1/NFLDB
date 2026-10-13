import type { PlayerChart } from '../../types'
import { zoneShade } from './playerChartStats'

type ZoneCell = { att: number; comp: number; yds: number; td: boolean; int: boolean }

const ZONE_BANDS = [
  { key: '20+', min: 20, max: Infinity },
  { key: '10–19', min: 10, max: 19.5 },
  { key: '0–9', min: 0, max: 9.5 },
  { key: 'Screen', min: -Infinity, max: -0.5 },
] as const

const ZONE_LANES = ['left', 'middle', 'right'] as const

function zoneData(events: PlayerChart['events']) {
  const cells = new Map<string, ZoneCell>()
  let plotted = 0
  for (const e of events) {
    const lane = (e.lane ?? '').toLowerCase()
    if (e.air_yards == null || !ZONE_LANES.includes(lane as typeof ZONE_LANES[number])) continue
    const band = ZONE_BANDS.find(b => e.air_yards! >= b.min && e.air_yards! <= b.max)
    if (!band) continue
    const key = `${band.key}|${lane}`
    const cell = cells.get(key) ?? { att: 0, comp: 0, yds: 0, td: false, int: false }
    cell.att += 1
    if (e.outcome === 'Complete' || e.outcome === 'TD') {
      cell.comp += 1
      cell.yds += Number(e.yards ?? 0)
    }
    if (e.outcome === 'TD') cell.td = true
    if (e.outcome === 'INT') cell.int = true
    cells.set(key, cell)
    plotted += 1
  }
  return { cells, plotted }
}

const MAP_H = 230

const LANE_X: Record<string, number> = { left: 18, middle: 50, right: 82 }

// Deterministic within-lane spread: consecutive depths take alternating
// offsets so dots never form a single-file column. Lane identity stays
// readable through the lane dividers, not dot position.
const LANE_JITTER = [0, -9, 9, -4.5, 4.5, -13, 13]

function mapDepth(ay: number) {
  return 30 + Math.min(33, Math.max(-4.5, ay)) * 5.4
}

export function TargetMap({ events, role }: { events: PlayerChart['events']; role: string }) {
  const lanes = new Map<string, { ay: number; outcome: string }[]>()
  for (const e of events) {
    const lane = (e.lane ?? '').toLowerCase()
    if (e.air_yards == null || !(lane in LANE_X)) continue
    lanes.set(lane, [...(lanes.get(lane) ?? []), { ay: e.air_yards, outcome: e.outcome }])
  }
  if (![...lanes.values()].some(l => l.length)) return null
  const dots: { x: number; b: number; outcome: string }[] = []
  for (const [lane, list] of lanes) {
    list.sort((a, b) => a.ay - b.ay)
    list.forEach((e, i) => dots.push({ x: LANE_X[lane] + LANE_JITTER[i % LANE_JITTER.length], b: mapDepth(e.ay), outcome: e.outcome }))
  }
  return (
    <div>
      <div className="micro">{role === 'passer' ? 'Passing map' : 'Target map'}</div>
      <div className="tmap" style={{ height: MAP_H }}>
        <span className="tm-lane-label" style={{ left: '18%' }}>Left</span>
        <span className="tm-lane-label" style={{ left: '50%' }}>Mid</span>
        <span className="tm-lane-label" style={{ left: '82%' }}>Right</span>
        {[10, 20, 30].map(d => <span key={d} className="tm-yard" style={{ bottom: mapDepth(d) }} />)}
        {[10, 20, 30].map(d => <span key={d} className="tm-depth" style={{ bottom: mapDepth(d) - 5 }}>{d}</span>)}
        <div className="tm-los" style={{ bottom: mapDepth(0) }} />
        <span className="tm-los-label" style={{ bottom: mapDepth(0) - 14 }}>LOS</span>
        {dots.map((d, i) => {
          const cls = d.outcome === 'TD' ? 'td' : d.outcome === 'INT' ? 'int' : d.outcome === 'Complete' ? 'catch' : 'miss'
          return <span key={i} className={`tm-dot ${cls}`} style={{ left: `${d.x}%`, bottom: d.b }}>{d.outcome === 'TD' ? '✦' : d.outcome === 'INT' ? '✕' : ''}</span>
        })}
      </div>
      <div className="legend">
        <span className="lg"><i className="tm-key catch" />Catch</span>
        <span className="lg"><i className="tm-key miss" />Incomplete</span>
        <span className="lg" style={{ color: 'var(--rate-good)' }}>✦ TD</span>
        <span className="lg" style={{ color: 'var(--rate-bad)' }}>✕ INT</span>
      </div>
    </div>
  )
}

export function ZoneGrid({ events }: { events: PlayerChart['events'] }) {
  const { cells, plotted } = zoneData(events)
  if (plotted === 0) return null
  return (
    <div className="zones-wrap">
      <div className="micro">By zone · comp/att</div>
      <div className="zones">
        <span className="zlab" /><span className="zlab col">Left</span><span className="zlab col">Middle</span><span className="zlab col">Right</span>
        {ZONE_BANDS.map(band => (
          <span key={band.key} style={{ display: 'contents' }}>
            <span className="zlab">{band.key}</span>
            {ZONE_LANES.map(lane => {
              const cell = cells.get(`${band.key}|${lane}`)
              if (!cell) return <div key={lane} className="zcell z0"><b>—</b></div>
              return <div key={lane} className={`zcell ${zoneShade(cell.att)}`}>
                {cell.td && <span className="zstar">✦</span>}
                {cell.int && <span className="zint">✕</span>}
                <b>{cell.comp}/{cell.att}</b>
                <small>{Math.round(cell.yds)} yds</small>
              </div>
            })}
          </span>
        ))}
        <span className="zone-los">Line of scrimmage</span>
      </div>
      <div className="legend"><span className="lg"><i style={{ background: '#403a6e' }} />More attempts</span></div>
    </div>
  )
}
