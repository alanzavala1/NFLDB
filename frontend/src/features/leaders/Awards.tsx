import { Link } from 'react-router-dom'
import type { LeagueLeader } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl } from '../../utils/teams'
import { PAST_AWARDS, AWARD_ORDER, AWARD_LABEL, type AwardKey, type AwardWinner } from '../../utils/awards'

function mvpScore(p: LeagueLeader): number {
  // QB-heavy formula but skill-position monsters can break in via rush/rec yards
  if (p.attempts >= 100) {
    return p.pass_yards + p.pass_tds * 20 - p.interceptions_thrown * 15 + p.rush_yards * 0.5 + p.rush_tds * 20 + (p.pass_epa ?? 0) * 5
  }
  if (p.carries + p.receptions >= 100) {
    return (p.rush_yards + p.rec_yards) + (p.rush_tds + p.rec_tds) * 25 + ((p.rush_epa ?? 0) + (p.rec_epa ?? 0)) * 5
  }
  return -Infinity
}

function opoyScore(p: LeagueLeader): number {
  if (p.position === 'QB') return -Infinity
  if (p.carries < 50 && (p.targets == null || p.targets < 30)) return -Infinity
  return (p.rush_yards + p.rec_yards) + (p.rush_tds + p.rec_tds) * 25 + ((p.rush_epa ?? 0) + (p.rec_epa ?? 0)) * 5
}

function dpoyScore(p: LeagueLeader): number {
  const tot = p.solo_tackles + p.assist_tackles
  if (tot < 20 && p.sacks < 5 && p.def_interceptions < 3) return -Infinity
  return p.sacks * 15 + p.tackles_for_loss * 5 + p.def_interceptions * 20 + p.qb_hits * 2 + p.pass_breakups * 3 + p.solo_tackles + p.assist_tackles * 0.5
}

interface RaceScorer { award: AwardKey; label: string; score: (p: LeagueLeader) => number; statLine: (p: LeagueLeader) => string }

const RACE_SCORERS: RaceScorer[] = [
  { award: 'MVP',  label: 'MVP Race',  score: mvpScore,  statLine: p => p.attempts >= 100
    ? `${p.pass_yards.toLocaleString()} YDS · ${p.pass_tds} TD · ${p.interceptions_thrown} INT`
    : `${(p.rush_yards + p.rec_yards).toLocaleString()} SCRIM · ${p.rush_tds + p.rec_tds} TD` },
  { award: 'OPOY', label: 'OPOY Race', score: opoyScore, statLine: p => `${(p.rush_yards + p.rec_yards).toLocaleString()} SCRIM · ${p.rush_tds + p.rec_tds} TD` },
  { award: 'DPOY', label: 'DPOY Race', score: dpoyScore, statLine: p => `${p.solo_tackles + p.assist_tackles} TKL · ${p.sacks} SCK · ${p.def_interceptions} INT` },
]

function AwardWinnerCard({ winner }: { winner: AwardWinner }) {
  const isMvp = winner.award === 'MVP'
  return (
    <div className={`rounded-xl border p-3.5 ${isMvp ? 'border-gold/40 bg-gold/5' : 'border-surface-line bg-surface-card'}`}>
      <div className={`text-[10px] font-black uppercase tracking-widest mb-2 ${isMvp ? 'text-gold' : 'text-ink-dim'}`}>
        {AWARD_LABEL[winner.award]}
      </div>
      <div className="flex items-center gap-2.5">
        <img src={teamLogoUrl(winner.team)} className="w-8 h-8 object-contain shrink-0" alt="" />
        <div className="min-w-0">
          <div className={`text-sm font-bold truncate ${isMvp ? 'text-ink' : 'text-ink'}`}>{winner.player}</div>
          <div className="text-[11px] text-ink-dim">{winner.team} · {winner.pos}</div>
        </div>
      </div>
    </div>
  )
}

function RaceCard({ scorer, leaders }: { scorer: RaceScorer; leaders: LeagueLeader[] }) {
  const top3 = [...leaders]
    .map(p => ({ p, s: scorer.score(p) }))
    .filter(x => x.s > -Infinity)
    .sort((a, b) => b.s - a.s)
    .slice(0, 3)
    .map(x => x.p)
  const isMvp = scorer.award === 'MVP'
  return (
    <div className={`rounded-xl border p-3.5 ${isMvp ? 'border-gold/40 bg-gold/5' : 'border-surface-line bg-surface-card'}`}>
      <div className={`text-[10px] font-black uppercase tracking-widest mb-2.5 ${isMvp ? 'text-gold' : 'text-ink-dim'}`}>
        {scorer.label}
      </div>
      {top3.length === 0
        ? <p className="text-xs text-ink-dim">No qualifying candidates yet</p>
        : (
          <div className="space-y-1.5">
            {top3.map((p, i) => (
              <Link key={p.player_id} to={`/players/${p.player_id}`}
                className="flex items-center gap-2 group hover:bg-surface-raise/40 rounded px-1 py-0.5 -mx-1 transition-colors">
                <span className={`text-[10px] font-black tabular-nums w-3 shrink-0 ${i === 0 ? 'text-gold' : 'text-ink-dim'}`}>{i + 1}</span>
                {p.headshot_url
                  ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-surface-raise" alt="" />
                  : <div className="w-7 h-7 rounded-full bg-surface-raise shrink-0" />
                }
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-ink group-hover:text-ink truncate transition-colors">{p.player_name}</div>
                  <div className="text-[10px] text-ink-dim truncate">{p.team} · {p.position} · {scorer.statLine(p)}</div>
                </div>
              </Link>
            ))}
          </div>
        )
      }
    </div>
  )
}

export function AwardsSection({ season, leaders }: { season: number; leaders: LeagueLeader[] }) {
  const past = PAST_AWARDS[season]
  const isPast = !!past

  if (isPast) {
    return (
      <Card title={`${season} Award Winners`} className="mb-8"><div className="grid grid-cols-2 gap-3 border-t border-surface-line p-4 sm:grid-cols-3 lg:grid-cols-6">
          {AWARD_ORDER.map(key => {
            const w = past.find(x => x.award === key)
            return w ? <AwardWinnerCard key={key} winner={w} /> : null
          })}
        </div></Card>
    )
  }

  // In-progress season: race view
  if (leaders.length === 0) return null
  return (
    <Card title={`${season} Award Races`} className="mb-8"><div className="border-t border-surface-line px-4 py-3 text-right">
        <span className="text-[10px] text-ink-dim uppercase tracking-widest">Stat-based · Voting decides actual winners</span>
      </div><div className="grid grid-cols-1 gap-3 border-t border-surface-line p-4 lg:grid-cols-3">
        {RACE_SCORERS.map(s => <RaceCard key={s.award} scorer={s} leaders={leaders} />)}
      </div></Card>
  )
}
