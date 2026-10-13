import { useMemo, useState } from 'react'
import type { GameDetail, GameLineup, LineupPlayer } from '../../types'
import { teamNickname, teamPrimaryColor } from '../../utils/teams'
import { ratingClass } from './formatting'
import { placePlayers } from './lineupPlacement'
import { LineupField } from './LineupField'
import { PlayerNode, RotationList } from './LineupPlayers'
import { PlayerChartModal } from './PlayerChartModal'

export default function GameLineupView({ game, lineup }: { game: GameDetail; lineup: GameLineup | null }) {
  const [ball, setBall] = useState<'away' | 'home'>('home')
  const [infoOpen, setInfoOpen] = useState(false)
  const [selected, setSelected] = useState<LineupPlayer | null>(null)

  const away = useMemo(() => lineup?.teams.find(t => t.team === game.away_team), [lineup, game.away_team])
  const home = useMemo(() => lineup?.teams.find(t => t.team === game.home_team), [lineup, game.home_team])
  if (!lineup || !away || !home) return <div className="lineup-card card">No lineup data is available for this game.</div>
  // Matchup view: the possessing team's offense on the bottom half, the
  // opposing defense mirrored on top — one real football situation at a time.
  const off = ball === 'away' ? away : home
  const def = ball === 'away' ? home : away
  const offense = placePlayers(off.offense, 'offense')
  const defense = placePlayers(def.defense, 'defense')

  return <>
    <div className="feed">
        <section className="lineup-card card">
          <div className="lu-head">
            <div className="side">
              <span className={`avg ${ratingClass(off.offense_avg)}`}>{off.offense_avg?.toFixed(1) ?? '-'}</span>
              <span className="chip" style={{ background: teamPrimaryColor(off.team) }}>{off.team}</span>
              <div><div className="tn">{teamNickname(off.team)} offense</div><div className="pers">{off.offense_personnel}</div></div>
            </div>
            <div className="side rt">
              <span className={`avg ${ratingClass(def.defense_avg)}`}>{def.defense_avg?.toFixed(1) ?? '-'}</span>
              <span className="chip" style={{ background: teamPrimaryColor(def.team) }}>{def.team}</span>
              <div><div className="tn">{teamNickname(def.team)} defense</div><div className="pers">{def.defense_personnel}</div></div>
            </div>
          </div>
          <div className="lu-chips">
            <button className={`upill ${ball === 'away' ? 'on' : ''}`} onClick={() => setBall('away')}><span className="mini" style={{ background: teamPrimaryColor(away.team) }} />{teamNickname(away.team)} ball</button>
            <button className={`upill ${ball === 'home' ? 'on' : ''}`} onClick={() => setBall('home')}><span className="mini" style={{ background: teamPrimaryColor(home.team) }} />{teamNickname(home.team)} ball</button>
            <button className="info-btn" onClick={(e) => { e.stopPropagation(); setInfoOpen(v => !v) }}>i<span className={`pop ${infoOpen ? 'open' : ''}`}><b>Game ratings</b> — every skill player, defender and kicker gets a 3.0–10.0 grade per game, computed from play-by-play <b>EPA</b> and defensive event stats, calibrated against 27 seasons. 6.5 is league average; 9.0+ is a top-2% performance. A <b>–</b> means the game gave too little to grade — a blocker who never touched the ball, or a target or two short of the minimum; hover it for the count. <b>Linemen share one unit grade</b> — public data records nothing per-blocker, so the line is graded on what it allows together: sacks, QB hits and stuffed runs versus league average. The field shows one team's offense against the other's defense; placement is the typical formation, not tracking.<span className="ramp"><span className="lg"><i style={{ background: 'var(--rate-bad)' }} />&lt;5.0</span><span className="lg"><i style={{ background: 'var(--rate-mid)' }} />5.0–6.9</span><span className="lg"><i style={{ background: 'var(--rate-good)' }} />7.0+</span><span className="lg"><i style={{ background: 'var(--rate-good)' }} />✦ 8.5+</span></span></span></button>
          </div>
          <div className="fieldwrap"><div className="fieldbox">
            <LineupField awayTeam={def.team} homeTeam={off.team} />
            {defense.map(p => <PlayerNode key={`d-${p.player_id ?? p.pfr_player_id}`} player={p} mirror onSelect={setSelected} />)}
            {offense.map(p => <PlayerNode key={`o-${p.player_id ?? p.pfr_player_id}`} player={p} mirror={false} onSelect={setSelected} />)}
            {off.ol_grade != null && <div className="ol-unit" style={{ left: '50%', top: '70.5%' }}><span className="micro">O-Line</span><span className={`val ${ratingClass(off.ol_grade)}`}>{off.ol_grade.toFixed(1)}</span></div>}
          </div></div>
          <div className="field-cap"><span className="glyph">◒</span> touchdown · offense vs the opposing defense · placement shows typical formation, not tracking · line grade is unit-level</div>
          {(lineup.away_coach || lineup.home_coach) && <div className="coach"><div><b>{lineup.away_coach}</b><br /><span>{away.team}</span></div><span className="micro">Coaches</span><div className="rt"><b>{lineup.home_coach}</b><br /><span>{home.team}</span></div></div>}
          <div className="rot-h micro">Rotation</div>
          <div className="rot"><RotationList team={away} /><RotationList team={home} /></div>
        </section>
    </div>
    <PlayerChartModal key={selected?.player_id ?? selected?.pfr_player_id ?? 'none'} game={game} player={selected} onClose={() => setSelected(null)} />
  </>
}
