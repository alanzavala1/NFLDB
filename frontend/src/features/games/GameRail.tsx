import type { ReactNode } from 'react'
import type { Game, GameDetail, GameLineup } from '../../types'
import { teamNickname, teamPrimaryColor } from '../../utils/teams'
import { roundTitle, roundLabel, spreadLabel, titleCase } from './formatting'

export function GameRail({ game, lineup, sameRound, scheduleFeedback }: { game: GameDetail; lineup: GameLineup; sameRound: Game[]; scheduleFeedback?: ReactNode }) {
  const yt = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${lineup.away_team} vs ${lineup.home_team} ${lineup.season} week ${lineup.week} highlights`)}`
  return <aside className="rail">
    <section className="card"><div className="card-h">Highlights <a className="micro act" href={yt} target="_blank" rel="noreferrer">YouTube ↗</a></div><a className="thumb" href={yt} target="_blank" rel="noreferrer"><span className="play"><i>▶</i></span><span className="tl">{lineup.away_team} vs {lineup.home_team} Game Highlights</span></a></section>
    <section className="card venue">
      <div className="card-h"><span className="glyph">⌖</span><div>{game.stadium ?? 'Venue'}</div></div>
      {game.surface && <div className="vrow"><span className="glyph">≋</span><span className="lab">Surface</span><span className="val">{titleCase(game.surface)}</span></div>}
      {game.roof && <div className="vrow"><span className="glyph">⌂</span><span className="lab">Roof</span><span className="val">{titleCase(game.roof)}</span></div>}
      {(game.temp != null || game.wind != null) && <div className="vrow"><span className="glyph">◌</span><span className="lab">Weather</span><span className="val">{game.temp != null ? `${game.temp}°F` : '-'}<small>{game.wind != null ? `wind ${game.wind} mph` : ''}</small></span></div>}
      {(game.spread_line != null || game.total_line != null) && <div className="vrow"><span className="glyph">⌁</span><span className="lab">Closing line</span><span className="val">{spreadLabel(game)}<small>{game.total_line != null ? `O/U ${game.total_line} · via nflverse` : 'via nflverse'}</small></span></div>}
    </section>
    <section className="card"><div className="card-h">{roundTitle(game)}</div>{scheduleFeedback}{sameRound.map(g => <div className={`row pg ${g.game_id === game.game_id ? 'cur' : ''}`} key={g.game_id} style={{ display: 'grid' }}><span className="lbl">{roundLabel(g.game_type)}</span><span className="m"><span className={`tline ${(g.away_score ?? 0) < (g.home_score ?? 0) ? 'dim' : ''}`}><span className="chip" style={{ background: teamPrimaryColor(g.away_team) }}>{g.away_team}</span>{teamNickname(g.away_team)}<span className="scr">{g.away_score ?? '-'}</span></span><span className={`tline ${(g.home_score ?? 0) < (g.away_score ?? 0) ? 'dim' : ''}`}><span className="chip" style={{ background: teamPrimaryColor(g.home_team) }}>{g.home_team}</span>{teamNickname(g.home_team)}<span className="scr">{g.home_score ?? '-'}</span></span></span><span className="ft">FT</span></div>)}</section>
  </aside>
}
