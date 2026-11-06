import type { TeamProfile } from '../../types'

export default function SeasonSummary({ profile }: { profile: TeamProfile }) {
  const playedGames = profile.games.filter(g => {
    return (g.away_team === profile.team ? g.away_score : g.home_score) !== null
  })
  const n = playedGames.length

  const pfTotal = playedGames.reduce((s, g) =>
    s + ((g.away_team === profile.team ? g.away_score : g.home_score) ?? 0), 0)
  const paTotal = playedGames.reduce((s, g) =>
    s + ((g.away_team === profile.team ? g.home_score : g.away_score) ?? 0), 0)

  const passYds  = profile.leaders.filter(p => p.attempts >= 1).reduce((s, p) => s + p.pass_yards, 0)
  const rushYds  = profile.leaders.filter(p => p.carries >= 1).reduce((s, p) => s + p.rush_yards, 0)
  const passTDs  = profile.leaders.filter(p => p.attempts >= 1).reduce((s, p) => s + p.pass_tds, 0)
  const rushTDs  = profile.leaders.filter(p => p.carries >= 1).reduce((s, p) => s + p.rush_tds, 0)
  const ints     = profile.leaders.filter(p => p.attempts >= 1).reduce((s, p) => s + p.interceptions_thrown, 0)
  const offEPA   = profile.leaders.reduce((s, p) => {
    if (p.pass_epa != null && p.attempts >= 1) s += p.pass_epa
    if (p.rush_epa != null && p.carries >= 1)  s += p.rush_epa
    return s
  }, 0)

  const diff = pfTotal - paTotal
  const boxes = [
    { label: 'PF/G',     val: n > 0 ? (pfTotal / n).toFixed(1) : '—' },
    { label: 'PA/G',     val: n > 0 ? (paTotal / n).toFixed(1) : '—' },
    { label: 'DIFF',     val: n > 0 ? `${diff >= 0 ? '+' : ''}${diff}` : '—', signed: true },
    { label: 'PASS YDS', val: passYds > 0 ? passYds.toLocaleString() : '—' },
    { label: 'RUSH YDS', val: rushYds > 0 ? rushYds.toLocaleString() : '—' },
    { label: 'TD',       val: (passTDs + rushTDs) || '—' },
    { label: 'INT',      val: ints || '—' },
    { label: 'OFF EPA',  val: offEPA !== 0 ? `${offEPA >= 0 ? '+' : ''}${offEPA.toFixed(1)}` : '—', signed: true },
  ]

  return (
    <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 mb-4">
      {boxes.map(b => {
        const str = String(b.val)
        const isPos = b.signed && str.startsWith('+')
        const isNeg = b.signed && str.startsWith('-')
        return (
          <div key={b.label} className="bg-surface-card border border-surface-line rounded-lg px-3 py-2.5 text-center">
            <div className={`text-sm font-bold tabular-nums ${isPos ? 'text-data-win' : isNeg ? 'text-data-loss' : 'text-ink'}`}>
              {b.val}
            </div>
            <div className="text-[10px] text-ink-dim uppercase tracking-wider mt-0.5 leading-tight">{b.label}</div>
          </div>
        )
      })}
    </div>
  )
}
