import type { NgsStats } from '../../types'
import Card from '../../components/Card'
import { passerRating, pct, type Totals } from './stats'

export default function HighlightsBar({ pos, totals, games, ngs, ranks }: {
  pos: string; totals: Totals; games: number; ngs: Record<number, NgsStats>
  ranks?: Record<string, string | null>  // map of stat label -> rank suffix
}) {
  const ngsEntries = Object.entries(ngs).sort(([a], [b]) => Number(b) - Number(a))
  const cpoeVals = ngsEntries.map(([, n]) => n.cpoe).filter((v): v is number => v != null)
  const avgCpoe = cpoeVals.length > 0 ? cpoeVals.reduce((a, b) => a + b, 0) / cpoeVals.length : null

  type Stat = { label: string; value: string | null; note?: string; green?: boolean; red?: boolean }
  let stats: Stat[] = []

  if (pos === 'QB') {
    const rate = passerRating(totals.completions, totals.attempts, totals.pass_yards, totals.pass_tds, totals.interceptions_thrown)
    const aya = totals.attempts > 0 ? (totals.pass_yards + 20 * totals.pass_tds - 45 * totals.interceptions_thrown) / totals.attempts : null
    const epaa = totals.attempts > 0 ? totals.pass_epa / totals.attempts : null
    stats = [
      { label: 'Passer Rating', value: rate },
      { label: 'AY/A', value: aya != null ? aya.toFixed(1) : null, note: 'Adj. Net Yds/Att' },
      { label: 'EPA / Att', value: epaa != null ? `${epaa >= 0 ? '+' : ''}${epaa.toFixed(3)}` : null, note: 'Exp. Points Added', green: epaa != null && epaa >= 0, red: epaa != null && epaa < 0 },
      { label: 'CPOE', value: avgCpoe != null ? `${avgCpoe >= 0 ? '+' : ''}${avgCpoe.toFixed(1)}%` : null, note: 'Cmp% Over Expected', green: avgCpoe != null && avgCpoe >= 0, red: avgCpoe != null && avgCpoe < 0 },
    ]
  } else if (pos === 'RB') {
    const epac = totals.carries > 0 ? totals.rush_epa / totals.carries : null
    const scryg = games > 0 ? (totals.rush_yards + totals.rec_yards) / games : null
    stats = [
      { label: 'Rush Yards', value: totals.rush_yards.toLocaleString() },
      { label: 'Y / Carry', value: totals.carries > 0 ? (totals.rush_yards / totals.carries).toFixed(1) : null },
      { label: 'EPA / Carry', value: epac != null ? `${epac >= 0 ? '+' : ''}${epac.toFixed(3)}` : null, note: 'Exp. Points Added', green: epac != null && epac >= 0, red: epac != null && epac < 0 },
      { label: 'SCR YDS / G', value: scryg != null ? scryg.toFixed(1) : null, note: 'Scrimmage per game' },
    ]
  } else if (pos === 'WR') {
    const epat = totals.targets > 0 ? totals.rec_epa / totals.targets : null
    stats = [
      { label: 'Rec Yards', value: totals.rec_yards.toLocaleString() },
      { label: 'Catch %', value: totals.targets > 0 ? pct(totals.receptions, totals.targets) + '%' : null },
      { label: 'EPA / Target', value: epat != null ? `${epat >= 0 ? '+' : ''}${epat.toFixed(3)}` : null, note: 'Exp. Points Added', green: epat != null && epat >= 0, red: epat != null && epat < 0 },
      { label: 'Y / Target', value: totals.targets > 0 ? (totals.rec_yards / totals.targets).toFixed(1) : null },
    ]
  } else if (pos === 'K') {
    const fgPct = totals.fg_att > 0 ? (totals.fg_made / totals.fg_att * 100).toFixed(1) : null
    const xpPct = totals.xp_att > 0 ? (totals.xp_made / totals.xp_att * 100).toFixed(1) : null
    const pts = totals.fg_made * 3 + totals.xp_made
    stats = [
      { label: 'FG Made', value: totals.fg_att > 0 ? `${totals.fg_made}/${totals.fg_att}` : null },
      { label: 'FG%', value: fgPct != null ? `${fgPct}%` : null },
      { label: 'XP Made', value: totals.xp_att > 0 ? `${totals.xp_made}/${totals.xp_att}` : null, note: xpPct != null ? `${xpPct}%` : undefined },
      { label: 'Points', value: pts > 0 ? pts.toLocaleString() : null },
    ]
  } else if (pos === 'P') {
    const avg = totals.punts > 0 ? (totals.punt_yards / totals.punts).toFixed(1) : null
    stats = [
      { label: 'Punts', value: totals.punts > 0 ? totals.punts.toString() : null },
      { label: 'Yards', value: totals.punt_yards > 0 ? totals.punt_yards.toLocaleString() : null },
      { label: 'Avg', value: avg != null ? `${avg} yds` : null, note: 'Yards per punt' },
      { label: 'Yds / G', value: games > 0 && totals.punts > 0 ? (totals.punt_yards / games).toFixed(1) : null },
    ]
  } else if (pos === 'OL') {
    stats = [
      { label: 'Games', value: games > 0 ? games.toLocaleString() : null, note: 'Career games played' },
    ]
  } else {
    const tot = totals.solo_tackles + totals.assist_tackles
    stats = [
      { label: 'Tackles', value: tot > 0 ? tot.toLocaleString() : null },
      { label: 'Sacks', value: totals.sacks > 0 ? totals.sacks.toString() : null },
      { label: 'INT', value: totals.def_interceptions > 0 ? totals.def_interceptions.toString() : null },
      { label: 'PBU', value: totals.pass_breakups > 0 ? totals.pass_breakups.toString() : null },
    ]
  }

  return (
    <Card title="Career highlights" className="mb-8"><div className="grid grid-cols-2 border-t border-surface-line sm:grid-cols-4">
      {stats.map(s => {
        const rank = ranks?.[s.label]
        return (
          <div key={s.label} className="border-b border-surface-line p-4 even:border-l sm:border-b-0 sm:border-l sm:first:border-l-0">
            <div className={`text-2xl font-black tabular-nums leading-none mb-1.5
              ${s.value == null ? 'text-ink-dim' : s.green ? 'text-data-win' : s.red ? 'text-data-loss' : 'text-ink'}`}>
              {s.value ?? '—'}
            </div>
            <div className="text-xs font-bold text-ink-dim uppercase tracking-wider">{s.label}</div>
            {s.note && <div className="text-xs text-ink-dim mt-0.5">{s.note}</div>}
            {rank && (
              <div className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-ink-dim">{rank}</div>
            )}
          </div>
        )
      })}
    </div></Card>
  )
}
