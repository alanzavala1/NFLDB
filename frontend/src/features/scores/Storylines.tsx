import { Link } from 'react-router-dom'
import type { Game } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl } from '../../utils/teams'
import { isFinished, gameWinner } from './presentation'

type Storyline = {
  tag: string
  title: string
  context: string
  game: Game
  logoTeam: string
}

function scoreLine(game: Game) {
  return `${game.away_team} ${game.away_score ?? '-'} – ${game.home_score ?? '-'} ${game.home_team}`
}

function spreadValue(value: number) {
  return Number.isInteger(value) ? value.toFixed(0) : value.toString()
}

function upsetLine(game: Game) {
  const winner = gameWinner(game)
  if (!winner || game.spread_line === null) return null
  const favorite = game.spread_line > 0 ? game.home_team : game.away_team
  const underdog = favorite === game.home_team ? game.away_team : game.home_team
  if (winner !== underdog) return null
  return `${winner} were +${spreadValue(Math.abs(game.spread_line))}`
}

function buildStorylines(weekGames: Game[], seasonGames: Game[], omitGameId?: string): Storyline[] {
  const weekFinished = weekGames.filter(isFinished)
  const seasonFinished = seasonGames.filter(isFinished)
  const scope = weekFinished.length < 3 ? seasonFinished : weekFinished
  const finished = scope.filter(game => game.game_id !== omitGameId)
  const stories: Storyline[] = []

  if (!finished.length) return stories

  const closest = [...finished].sort((a, b) => {
    const marginA = Math.abs(a.away_score! - a.home_score!)
    const marginB = Math.abs(b.away_score! - b.home_score!)
    return marginA - marginB || (b.away_score! + b.home_score!) - (a.away_score! + a.home_score!)
  })[0]
  if (closest) {
    const margin = Math.abs(closest.away_score! - closest.home_score!)
    const result = margin === 0 ? 'Tied' : `${margin}-point game`
    stories.push({
      tag: 'Thriller',
      title: scoreLine(closest),
      context: [`Week ${closest.week}`, result, closest.overtime === 1 ? 'OT' : null].filter(Boolean).join(' · '),
      game: closest,
      logoTeam: gameWinner(closest) ?? closest.away_team,
    })
  }

  const shootout = [...finished]
    .filter(game => !stories.some(story => story.game.game_id === game.game_id))
    .sort((a, b) => (b.away_score! + b.home_score!) - (a.away_score! + a.home_score!))[0]
  if (shootout) {
    stories.push({
      tag: 'Shootout',
      title: scoreLine(shootout),
      context: `Week ${shootout.week} · ${shootout.away_score! + shootout.home_score!} combined points`,
      game: shootout,
      logoTeam: gameWinner(shootout) ?? shootout.away_team,
    })
  }

  const upsets = finished
    .filter(game => game.spread_line !== null && game.spread_line !== 0)
    .filter(game => {
      const favorite = game.spread_line! > 0 ? game.home_team : game.away_team
      return gameWinner(game) !== favorite
    })
    .filter(game => !stories.some(story => story.game.game_id === game.game_id))
    .sort((a, b) => Math.abs(b.spread_line!) - Math.abs(a.spread_line!))
  const upset = upsets[0]
  if (upset) {
    stories.push({
      tag: 'Upset',
      title: scoreLine(upset),
      context: `Week ${upset.week} · ${upsetLine(upset) ?? 'Underdog won'}`,
      game: upset,
      logoTeam: gameWinner(upset) ?? upset.away_team,
    })
  }

  return stories.slice(0, 3)
}

export function StorylinesCard({ weekGames, seasonGames, omitGameId }: { weekGames: Game[]; seasonGames: Game[]; omitGameId?: string }) {
  const stories = buildStorylines(weekGames, seasonGames, omitGameId)
  if (!stories.length) return null

  return (
    <Card title="Storylines">
      <div className="grid grid-cols-3 max-[780px]:grid-cols-1">
        {stories.map((story, index) => (
          <Link
            key={`${story.tag}-${story.game.game_id}`}
            to={`/games/${story.game.game_id}`}
            className={`border-t border-surface-line px-4 py-4 text-inherit no-underline transition-colors hover:bg-surface-raise ${index > 0 ? 'min-[781px]:border-l' : ''}`}
          >
            <div className="mb-2 flex items-center gap-2">
              <img src={teamLogoUrl(story.logoTeam)} className="h-6 w-6 object-contain" alt="" />
              <span className="ml-auto text-[10px] font-bold uppercase tracking-[0.14em] text-indigo-300">{story.tag}</span>
            </div>
            <div className="truncate text-sm font-black text-ink">{story.title}</div>
            <div className="mt-1 truncate text-xs text-ink-dim">{story.context}</div>
          </Link>
        ))}
      </div>
    </Card>
  )
}
