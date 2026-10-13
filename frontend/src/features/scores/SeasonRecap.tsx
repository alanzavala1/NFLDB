import Card, { CardRow } from '../../components/Card'
import { AWARD_LABEL, AWARD_ORDER, PAST_AWARDS, SB_CHAMPS } from '../../utils/awards'
import { teamLogoUrl, teamName } from '../../utils/teams'

export function LastSeasonRecap({ season }: { season: number }) {
  const previous = season - 1
  const champion = SB_CHAMPS[previous]
  const awards = PAST_AWARDS[previous] ?? []
  if (!champion && !awards.length) return null

  return (
    <Card title={`${previous} recap`}>
      {champion && (
        <CardRow className="justify-between">
          <div className="flex min-w-0 items-center gap-2.5">
            <img src={teamLogoUrl(champion.team)} className="h-8 w-8 shrink-0 object-contain" alt="" />
            <div className="min-w-0">
              <div className="truncate text-sm font-bold text-ink">{teamName(champion.team)}</div>
              <div className="text-xs text-ink-dim">Super Bowl champion</div>
            </div>
          </div>
          <div className="text-sm font-black tabular-nums text-gold">{champion.score}</div>
        </CardRow>
      )}
      {AWARD_ORDER.slice(0, 3).map(award => {
        const winner = awards.find(item => item.award === award)
        if (!winner) return null
        return (
          <CardRow key={award} className="justify-between">
            <div className="min-w-0">
              <div className="truncate text-sm font-bold text-ink">{winner.player}</div>
              <div className="text-xs text-ink-dim">{AWARD_LABEL[award]}</div>
            </div>
            <div className="flex items-center gap-1.5 text-xs font-bold text-ink-mid">
              <img src={teamLogoUrl(winner.team)} className="h-5 w-5 object-contain" alt="" />
              {winner.team}
            </div>
          </CardRow>
        )
      })}
    </Card>
  )
}
