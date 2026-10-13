import type { TeamProfile } from '../../types'
import { gameResult, weekLabel } from './selectors'
import { Link } from 'react-router-dom'
import { teamLogoUrl } from '../../utils/teams'

export default function SchedulePanel({ profile }: { profile: TeamProfile }) {
  let w = 0, l = 0, t = 0
  return (
    <div className="overflow-y-auto divide-y divide-surface-line/60 flex-1 min-h-0">
      {profile.games.map(g => {
        const isAway = g.away_team === profile.team
        const opponent = isAway ? g.home_team : g.away_team
        const teamScore = isAway ? g.away_score : g.home_score
        const oppScore = isAway ? g.home_score : g.away_score
        const result = gameResult(g, profile.team)
        const finished = teamScore !== null && oppScore !== null
        const resultColor = result === 'W' ? 'text-green-400' : result === 'L' ? 'text-data-loss' : 'text-ink-mid'

        if (result === 'W') w++
        else if (result === 'L') l++
        else if (result === 'T') t++
        const runningRec = finished ? (t > 0 ? `${w}-${l}-${t}` : `${w}-${l}`) : null

        return (
          <Link
            key={g.game_id}
            to={`/games/${g.game_id}`}
            className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-raise/50 transition-colors group"
          >
            <span className="text-xs text-ink-dim w-14 shrink-0">{weekLabel(g.week, g.game_type)}</span>
            <img src={teamLogoUrl(opponent)} alt={opponent} className="w-5 h-5 object-contain shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
            <span className="text-sm text-ink-mid flex-1 group-hover:text-ink transition-colors">
              {isAway ? '@' : 'vs'} {opponent}
            </span>
            {finished ? (
              <>
                <span className={`text-xs font-bold w-4 text-center ${resultColor}`}>{result}</span>
                <span className="text-xs tabular-nums text-ink-dim w-12 text-right">{teamScore}–{oppScore}</span>
                <span className="text-xs tabular-nums text-ink-dim w-10 text-right">{runningRec}</span>
              </>
            ) : (
              <span className="text-xs text-ink-dim w-16 text-right">{g.gameday}</span>
            )}
          </Link>
        )
      })}
    </div>
  )
}
