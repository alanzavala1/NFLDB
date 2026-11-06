import type { DivisionStandings, LeagueLeader, PowerRankingRow, StandingsRow } from '../../types'
import { hasReceivingActivity } from '../../utils/receiving'
import Card, { CardRow } from '../../components/Card'
import { QueryFailure } from '../../components/QueryFeedback'
import { teamLogoUrl, teamNickname } from '../../utils/teams'
import { MICRO } from './presentation'

type SectionRequestState = {
  loading: boolean
  error: Error | null
  onRetry: () => void
}

type LeaderCategory = {
  label: string
  unit: string
  filter: (leader: LeagueLeader) => boolean
  value: (leader: LeagueLeader) => number
  display: (leader: LeagueLeader) => string
}

const LEADER_CATEGORIES: LeaderCategory[] = [
  { label: 'Passing',   unit: 'YDS', filter: p => p.attempts >= 100, value: p => p.pass_yards, display: p => p.pass_yards.toLocaleString() },
  { label: 'Rushing',   unit: 'YDS', filter: p => p.carries >= 50,   value: p => p.rush_yards, display: p => p.rush_yards.toLocaleString() },
  { label: 'Receiving', unit: 'YDS', filter: p => hasReceivingActivity(p, 20), value: p => p.rec_yards, display: p => p.rec_yards.toLocaleString() },
  { label: 'Defense',   unit: 'TKL', filter: p => p.solo_tackles + p.assist_tackles >= 10, value: p => p.solo_tackles + p.assist_tackles, display: p => (p.solo_tackles + p.assist_tackles).toString() },
]

function leaderInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join('')
    .toUpperCase()
}

function formatRecord(row: StandingsRow) {
  return `${row.w}-${row.l}${row.t ? `-${row.t}` : ''}`
}

function formatNetEpa(value: number | null | undefined) {
  if (value == null) return '--'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}

function movementMeta(movement: number | null | undefined) {
  if (!movement) return { text: '—', className: 'text-ink-dim' }
  if (movement > 0) return { text: `▲ ${movement}`, className: 'text-data-win' }
  return { text: `▼ ${Math.abs(movement)}`, className: 'text-data-loss' }
}

function pointDiff(row: StandingsRow) {
  return row.pf - row.pa
}

function formatPointDiff(row: StandingsRow) {
  const diff = pointDiff(row)
  return `${diff > 0 ? '+' : ''}${diff}`
}

function divisionSort(division: string) {
  const order = ['East', 'North', 'South', 'West']
  const suffix = division.split(' ').at(-1) ?? division
  const index = order.indexOf(suffix)
  return index === -1 ? order.length : index
}

export function TeamsCard({ rankings, loading, error, onRetry }: { rankings: PowerRankingRow[] | undefined } & SectionRequestState) {
  const topTeams = rankings?.slice(0, 10) ?? []

  return (
    <Card title="Power rankings" action={<span className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-dim">EPA</span>}>
      <QueryFailure resource="power rankings" error={error} hasData={rankings !== undefined} onRetry={onRetry} />
      {topTeams.length ? topTeams.map(team => {
        const movement = movementMeta(team.movement)
        return (
        <CardRow key={team.team} to={`/teams/${team.team}`} className="!grid grid-cols-[20px_28px_minmax(0,1fr)_38px_48px] gap-2">
          <span className="text-right text-xs font-bold tabular-nums text-ink-dim">{team.rank}</span>
          <img src={teamLogoUrl(team.team)} className="h-7 w-7 shrink-0 object-contain" alt="" />
          <span className="min-w-0">
            <span className="block truncate text-sm font-bold text-ink">{teamNickname(team.team)}</span>
            <span className="block text-[11px] font-bold tabular-nums text-ink-dim">{team.record}</span>
          </span>
          <span className={`text-right text-[11px] font-black tabular-nums ${movement.className}`}>{movement.text}</span>
          <span className={`text-right text-xs font-black tabular-nums ${(team.net_epa_play ?? 0) >= 0 ? 'text-data-win' : 'text-data-loss'}`}>
            {formatNetEpa(team.net_epa_play)}
          </span>
        </CardRow>
        )
      }) : error && rankings === undefined ? null : (
        <CardRow className="text-sm text-ink-dim">{loading ? 'Power rankings loading...' : 'No rankings found'}</CardRow>
      )}
      {topTeams.length > 0 && (
        <div className="border-t border-surface-line px-4 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-dim">
          Net EPA per play · updated weekly
        </div>
      )}
    </Card>
  )
}

export function ConferenceLeadersCard({
  conference,
  standings,
  season,
  loading,
  error,
  onRetry,
}: {
  conference: 'AFC' | 'NFC'
  standings: DivisionStandings[] | undefined
  season: number
} & SectionRequestState) {
  const leaders = (standings ?? [])
    .filter(group => group.division.startsWith(conference))
    .sort((a, b) => divisionSort(a.division) - divisionSort(b.division))
    .map(group => ({ division: group.division.replace(`${conference} `, ''), team: group.teams[0] }))
    .filter((entry): entry is { division: string; team: StandingsRow } => Boolean(entry.team))

  const tagClass = conference === 'AFC' ? 'bg-surface-raise' : 'bg-surface-raise'

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <span className={`grid h-5 w-5 place-items-center rounded-md text-[8.5px] font-black text-white ${tagClass}`}>{conference}</span>
          <span>Division leaders</span>
        </span>
      }
      action={{ label: 'Full standings', to: `/standings?season=${season}` }}
    >
      <QueryFailure resource="standings" error={error} hasData={standings !== undefined} onRetry={onRetry} />
      {leaders.length ? (
        <>
          <div className={`${MICRO} grid grid-cols-[42px_minmax(0,1fr)_40px_44px] gap-2 border-t border-surface-line px-4 py-2`}>
            <span />
            <span>Team</span>
            <span className="text-right">W-L</span>
            <span className="text-right">Diff</span>
          </div>
          {leaders.map(entry => (
            <CardRow
              key={`${conference}-${entry.division}`}
              to={`/teams/${entry.team.team}`}
              className="!grid grid-cols-[42px_minmax(0,1fr)_40px_44px] gap-2"
            >
              <span className={MICRO}>{entry.division}</span>
              <span className="flex min-w-0 items-center gap-2 text-sm font-bold text-ink">
                <img src={teamLogoUrl(entry.team.team)} className="h-6 w-6 shrink-0 object-contain" alt="" />
                <span className="truncate">{teamNickname(entry.team.team)}</span>
              </span>
              <span className="text-right text-xs font-bold tabular-nums text-ink">{formatRecord(entry.team)}</span>
              <span className={`text-right text-xs font-black tabular-nums ${pointDiff(entry.team) >= 0 ? 'text-data-win' : 'text-data-loss'}`}>
                {formatPointDiff(entry.team)}
              </span>
            </CardRow>
          ))}
        </>
      ) : error && standings === undefined ? null : (
        <CardRow className="text-sm text-ink-dim">{loading ? 'Standings loading...' : 'No leaders found'}</CardRow>
      )}
    </Card>
  )
}

function LeaderFace({ leader }: { leader: LeagueLeader }) {
  if (leader.headshot_url) {
    return <img src={leader.headshot_url} className="h-9 w-9 shrink-0 rounded-full bg-surface-raise object-cover object-top" alt="" />
  }
  return (
    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-raise text-xs font-black text-ink-mid">
      {leaderInitials(leader.player_name)}
    </div>
  )
}

export function LeagueLeadersCard({ season, leaders, loading, error, onRetry }: { season: number; leaders: LeagueLeader[] | undefined } & SectionRequestState) {
  const tops = LEADER_CATEGORIES
    .map(category => ({ category, leader: (leaders ?? []).filter(category.filter).sort((a, b) => category.value(b) - category.value(a))[0] }))
    .filter((entry): entry is { category: LeaderCategory; leader: LeagueLeader } => Boolean(entry.leader))

  return (
    <Card title="League leaders" action={{ label: 'All leaders', to: `/leaders?season=${season}` }}>
      <QueryFailure resource="league leaders" error={error} hasData={leaders !== undefined} onRetry={onRetry} />
      {tops.length ? tops.map(({ category, leader }) => (
        <CardRow key={category.label} to={`/players/${leader.player_id}`} className="justify-between">
          <div className="flex min-w-0 items-center gap-2.5">
            <LeaderFace leader={leader} />
            <div className="min-w-0">
              <div className="truncate text-sm font-bold text-ink">{leader.player_name}</div>
              <div className="truncate text-xs text-ink-dim">{[leader.team, category.label].filter(Boolean).join(' - ')}</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-lg font-black tabular-nums text-ink">{category.display(leader)}</div>
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-dim">{category.unit}</div>
          </div>
        </CardRow>
      )) : error && leaders === undefined ? null : (
        <CardRow className="text-sm text-ink-dim">{loading ? 'Leaders loading...' : 'No leaders found'}</CardRow>
      )}
    </Card>
  )
}
