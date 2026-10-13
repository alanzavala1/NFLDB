import type { GameLineup, LineupScoringEvent } from '../../types'
import { lastName } from './formatting'

function scoringByTeam(scoring: LineupScoringEvent[], team: string) {
  const tds = scoring.filter(s => s.team === team && s.kind === 'TD')
  const fgs = new Map<string, LineupScoringEvent[]>()
  for (const s of scoring.filter(s => s.team === team && s.kind === 'FG')) {
    const key = s.player_id ?? s.player_name ?? team
    fgs.set(key, [...(fgs.get(key) ?? []), s])
  }
  return { tds, fgs: [...fgs.values()] }
}

export function GameScorers({ lineup }: { lineup: GameLineup }) {
  const away = scoringByTeam(lineup.scoring, lineup.away_team)
  const home = scoringByTeam(lineup.scoring, lineup.home_team)
  const col = (data: ReturnType<typeof scoringByTeam>, right = false) => (
    <div className={`sc-col ${right ? 'rt' : ''}`}>
      {data.tds.map((s, i) => <span className="sc" key={`td-${i}`}><span className="glyph">◒</span><b>{lastName(s.player_name)}</b><span className="t">Q{s.qtr} {s.clock}</span></span>)}
      {data.fgs.map((group, i) => <span className="sc" key={`fg-${i}`}><span className="glyph">╋</span><b>{lastName(group[0].player_name)}</b><span className="t">{group.map(s => s.distance).filter(Boolean).join(', ')}</span></span>)}
    </div>
  )
  return <div className="lineup-scorers scorers">{col(away)}<div />{col(home, true)}</div>
}
