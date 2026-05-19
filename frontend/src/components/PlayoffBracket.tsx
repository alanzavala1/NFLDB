import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { Game, WeekGroup } from '../api'
import { teamLogoUrl, CONFERENCES } from '../utils/teams'

export type ConfKey = 'AFC' | 'NFC'

export function teamConference(team: string): ConfKey | null {
  for (const conf of ['AFC', 'NFC'] as const) {
    for (const teams of Object.values(CONFERENCES[conf])) {
      if (teams.includes(team)) return conf
    }
  }
  return null
}

export const CONF_STYLE: Record<ConfKey, { text: string; dot: string }> = {
  AFC: { text: 'text-rose-300',   dot: 'bg-rose-400'   },
  NFC: { text: 'text-indigo-300', dot: 'bg-indigo-400' },
}

function pickWinner(g: Game): string | null {
  if (g.away_score === null || g.home_score === null) return null
  if (g.away_score === g.home_score) return null
  return g.away_score > g.home_score ? g.away_team : g.home_team
}

function toRoman(n: number): string {
  const pairs: [number, string][] = [
    [1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'],
    [100, 'C'], [90, 'XC'], [50, 'L'], [40, 'XL'],
    [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I'],
  ]
  let s = ''
  for (const [v, sym] of pairs) {
    while (n >= v) { s += sym; n -= v }
  }
  return s
}

interface ChampInfo { afc: string | null; nfc: string | null; sb: string | null }

function PlayoffGameCard({ game }: { game: Game }) {
  const finished = game.away_score !== null && game.home_score !== null
  const awayWon = finished && game.away_score! > game.home_score!
  const homeWon = finished && game.home_score! > game.away_score!
  const rows = [
    { team: game.away_team, score: game.away_score, won: awayWon },
    { team: game.home_team, score: game.home_score, won: homeWon },
  ]
  return (
    <Link
      to={`/games/${game.game_id}`}
      className="block bg-gray-900 border border-gray-800 rounded-md hover:border-gray-600 transition-colors overflow-hidden"
    >
      <div className="px-2.5 py-1.5 space-y-1">
        {rows.map(t => (
          <div key={t.team} className={`flex items-center gap-2 ${finished && !t.won ? 'opacity-45' : ''}`}>
            <img src={teamLogoUrl(t.team)} alt={t.team} className="w-5 h-5 object-contain shrink-0" />
            <span className={`text-xs font-semibold flex-1 ${t.won ? 'text-white' : 'text-gray-400'}`}>{t.team}</span>
            <span className={`text-sm font-bold tabular-nums ${t.won ? 'text-white' : 'text-gray-500'}`}>
              {t.score ?? '—'}
            </span>
          </div>
        ))}
      </div>
    </Link>
  )
}

function BracketRound({ label, games }: { label: string; games: Game[] }) {
  if (!games.length) return null
  return (
    <div className="flex-1 min-w-0 flex flex-col">
      <div className="text-[10px] font-bold uppercase tracking-widest mb-2 text-center text-gray-600">
        {label}
      </div>
      <div className="flex-1 flex flex-col justify-around gap-3">
        {games.map(g => <PlayoffGameCard key={g.game_id} game={g} />)}
      </div>
    </div>
  )
}

function ConferenceBracket({ conf, games, champs, side = 'left' }: { conf: ConfKey; games: Game[]; champs: ChampInfo; side?: 'left' | 'right' }) {
  const wc  = games.filter(g => g.game_type === 'WC')
  const div = games.filter(g => g.game_type === 'DIV')
  const con = games.filter(g => g.game_type === 'CON')
  if (!wc.length && !div.length && !con.length) return null
  const style = CONF_STYLE[conf]
  const champTeam = conf === 'AFC' ? champs.afc : champs.nfc
  const reverseCls = side === 'right' ? 'lg:flex-row-reverse' : ''
  return (
    <div>
      <div className={`flex items-center gap-2 mb-3 pb-2 border-b border-gray-800 ${reverseCls}`}>
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${style.dot}`} />
        <span className={`text-sm font-bold uppercase tracking-widest ${style.text}`}>{conf}</span>
        <div className="flex-1" />
        {champTeam && (
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">
            Champion <span className="text-white font-bold">{champTeam}</span>
          </span>
        )}
      </div>
      <div className={`flex gap-2 ${reverseCls}`}>
        <BracketRound label="Wild Card"  games={wc} />
        <BracketRound label="Divisional" games={div} />
        <BracketRound label="Conference" games={con} />
      </div>
    </div>
  )
}

function SuperBowlCard({ game, champ, season }: { game: Game; champ: string | null; season: number }) {
  const finished = game.away_score !== null && game.home_score !== null
  const sbNumber = season - 1965  // Season 1966 → SB I
  const rows = [
    { team: game.away_team, score: game.away_score, won: finished && game.away_score! > game.home_score! },
    { team: game.home_team, score: game.home_score, won: finished && game.home_score! > game.away_score! },
  ]
  return (
    <Link
      to={`/games/${game.game_id}`}
      className="block rounded-xl border border-yellow-500/50 bg-gray-900 hover:bg-gray-900/80 transition-colors overflow-hidden"
    >
      <div className="px-4 py-2 border-b border-yellow-500/30 bg-yellow-500/10 text-center">
        <span className="text-xs font-bold uppercase tracking-[0.25em] text-yellow-300">
          Super Bowl {sbNumber > 0 ? toRoman(sbNumber) : ''}
        </span>
      </div>
      <div className="p-4 space-y-2.5">
        {rows.map(t => (
          <div key={t.team} className={`flex items-center gap-3 ${finished && !t.won ? 'opacity-50' : ''}`}>
            <img src={teamLogoUrl(t.team)} alt={t.team} className="w-9 h-9 object-contain shrink-0" />
            <span className={`text-base font-bold flex-1 ${t.won ? 'text-white' : 'text-gray-400'}`}>{t.team}</span>
            <span className={`text-2xl font-black tabular-nums ${t.won ? 'text-white' : 'text-gray-500'}`}>
              {t.score ?? '—'}
            </span>
          </div>
        ))}
      </div>
      {champ && (
        <div className="px-4 py-2 border-t border-yellow-500/30 bg-yellow-500/10 text-center">
          <span className="text-xs font-bold uppercase tracking-widest text-yellow-300">
            <span className="text-white">{champ}</span> · Champions
          </span>
        </div>
      )}
    </Link>
  )
}

export function PlayoffBracket({ season, title }: { season: number; title?: string }) {
  const [weeks, setWeeks] = useState<WeekGroup[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setWeeks([])
    api.schedule(season)
      .then(setWeeks)
      .catch(() => setWeeks([]))
      .finally(() => setLoading(false))
  }, [season])

  if (loading) return null

  const playoffGames = weeks
    .flatMap(w => w.games)
    .filter(g => g.game_type === 'WC' || g.game_type === 'DIV' || g.game_type === 'CON' || g.game_type === 'SB')

  if (!playoffGames.length) return null

  playoffGames.sort((a, b) => a.week - b.week || (a.gametime ?? '').localeCompare(b.gametime ?? ''))

  const afc = playoffGames.filter(g => g.game_type !== 'SB' && teamConference(g.home_team) === 'AFC')
  const nfc = playoffGames.filter(g => g.game_type !== 'SB' && teamConference(g.home_team) === 'NFC')
  const sb  = playoffGames.find(g => g.game_type === 'SB') ?? null

  const afcConGame = afc.find(g => g.game_type === 'CON')
  const nfcConGame = nfc.find(g => g.game_type === 'CON')
  const champs: ChampInfo = {
    afc: afcConGame ? pickWinner(afcConGame) : null,
    nfc: nfcConGame ? pickWinner(nfcConGame) : null,
    sb:  sb ? pickWinner(sb) : null,
  }

  return (
    <div className="mb-10">
      <div className="flex items-center gap-3 mb-5">
        <h2 className="text-xl font-black text-white tracking-tight">{title ?? `${season} Playoffs`}</h2>
        <div className="flex-1 h-px bg-gray-800" />
        <span className="text-[10px] text-gray-500 uppercase tracking-widest">
          {playoffGames.length} game{playoffGames.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_minmax(260px,auto)_1fr] gap-4 items-center">
        <ConferenceBracket conf="AFC" games={afc} champs={champs} side="left" />
        {sb
          ? <SuperBowlCard game={sb} champ={champs.sb} season={season} />
          : <div className="hidden lg:block" />}
        <ConferenceBracket conf="NFC" games={nfc} champs={champs} side="right" />
      </div>
    </div>
  )
}
