import type { GameDetail } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl } from '../../utils/teams'
import { teamTotals } from './selectors'

function StatBar({ label, a, h, lo = false, neutral = false }: {
  label: string; a: string | number; h: string | number; lo?: boolean; neutral?: boolean
}) {
  const av = typeof a === 'number' ? a : parseFloat(String(a)) || 0
  const hv = typeof h === 'number' ? h : parseFloat(String(h)) || 0
  const total = av + hv
  const aPct = total > 0 ? (av / total) * 100 : 50
  const hPct = total > 0 ? (hv / total) * 100 : 50
  const aWon = !neutral && av !== hv && (lo ? av < hv : av > hv)
  const hWon = !neutral && av !== hv && (lo ? hv < av : hv > av)
  return (
    <div className="px-5 py-2.5">
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <span className={`text-base font-bold tabular-nums w-20 text-right ${aWon ? 'text-white' : 'text-ink-dim'}`}>{a}</span>
        <span className="text-[10px] font-semibold text-ink-dim uppercase tracking-wider text-center">{label}</span>
        <span className={`text-base font-bold tabular-nums w-20 text-left ${hWon ? 'text-white' : 'text-ink-dim'}`}>{h}</span>
      </div>
      {!neutral && total > 0 && (
        <div className="relative h-1 rounded-full bg-surface-raise/60 overflow-hidden flex">
          <div className={`h-full ${aWon ? 'bg-data-win' : 'bg-data-loss/30'}`} style={{ width: `${aPct}%` }} />
          <div className={`h-full ${hWon ? 'bg-data-win' : 'bg-data-loss/30'}`} style={{ width: `${hPct}%` }} />
        </div>
      )}
    </div>
  )
}

function SectionDivider({ label }: { label: string }) {
  return (
    <div className="px-5 pt-3 pb-1 text-center text-[10px] font-bold text-ink-dim uppercase tracking-widest border-t border-surface-line/40 mt-1">
      {label}
    </div>
  )
}

export function BoxScore({ game }: { game: GameDetail }) {
  const A = teamTotals(game.away)
  const H = teamTotals(game.home)
  if (!A.passAtt && !A.rushCar && !H.passAtt && !H.rushCar) return null
  const AS = game.team_stats?.find(t => t.team === game.away_team)
  const HS = game.team_stats?.find(t => t.team === game.home_team)
  const ypp = (yds: number, plays?: number) => plays ? (yds / plays).toFixed(1) : '—'
  const epaFmt = (v: number | null | undefined) => v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`

  return (
    <Card className="mb-4">
      {/* Header */}
      <div className="flex items-center border-b border-surface-line bg-surface-raise/40">
        <div className="flex-1 flex items-center justify-end gap-2 px-5 py-3">
          <span className="font-bold text-white text-sm">{game.away_team}</span>
          <img src={teamLogoUrl(game.away_team)} className="w-6 h-6 object-contain" alt="" />
        </div>
        <div className="w-28 text-center text-[10px] font-bold text-ink-dim uppercase tracking-widest shrink-0">
          Team Stats
        </div>
        <div className="flex-1 flex items-center justify-start gap-2 px-5 py-3">
          <img src={teamLogoUrl(game.home_team)} className="w-6 h-6 object-contain" alt="" />
          <span className="font-bold text-white text-sm">{game.home_team}</span>
        </div>
      </div>

      <div className="pb-3">
        <StatBar label="Total Yards"   a={A.totalYds} h={H.totalYds} />
        {AS && HS && (
          <>
            <StatBar label="Total Plays"  a={AS.plays} h={HS.plays} neutral />
            <StatBar label="Yards / Play" a={ypp(A.totalYds, AS.plays)} h={ypp(H.totalYds, HS.plays)} />
            <StatBar label="First Downs"  a={AS.first_downs} h={HS.first_downs} />
            <StatBar label="3rd Down"     a={`${AS.third_conv}/${AS.third_att}`} h={`${HS.third_conv}/${HS.third_att}`} neutral />
            {(AS.fourth_att > 0 || HS.fourth_att > 0) &&
              <StatBar label="4th Down"   a={`${AS.fourth_conv}/${AS.fourth_att}`} h={`${HS.fourth_conv}/${HS.fourth_att}`} neutral />}
            <StatBar label="Turnovers"    a={AS.turnovers} h={HS.turnovers} lo />
            <StatBar label="Penalties"    a={`${AS.penalties}-${AS.penalty_yards}`} h={`${HS.penalties}-${HS.penalty_yards}`} lo />
            <SectionDivider label="Efficiency" />
            <StatBar label="EPA / Play"    a={epaFmt(AS.epa_play)} h={epaFmt(HS.epa_play)} />
            <StatBar label="Success Rate"  a={`${AS.success_pct ?? 0}%`} h={`${HS.success_pct ?? 0}%`} />
          </>
        )}
        <SectionDivider label="Passing" />
        <StatBar label="Comp / Att"    a={`${A.passCmp}/${A.passAtt}`} h={`${H.passCmp}/${H.passAtt}`} neutral />
        <StatBar label="Yards"         a={A.passYds}    h={H.passYds} />
        <StatBar label="Touchdowns"    a={A.passTDs}    h={H.passTDs} />
        <StatBar label="Interceptions" a={A.ints}       h={H.ints}       lo />
        <StatBar label="Sacks Taken"   a={A.sacksTaken} h={H.sacksTaken} lo />
        <SectionDivider label="Rushing" />
        <StatBar label="Carries"       a={A.rushCar}  h={H.rushCar}  neutral />
        <StatBar label="Yards"         a={A.rushYds}  h={H.rushYds} />
        <StatBar label="Touchdowns"    a={A.rushTDs}  h={H.rushTDs} />
        <SectionDivider label="Defense" />
        <StatBar label="Sacks"         a={A.sacks}   h={H.sacks} />
        <StatBar label="Interceptions" a={A.defInts} h={H.defInts} />
      </div>
    </Card>
  )
}
