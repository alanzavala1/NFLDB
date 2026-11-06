import { AreaChart, Area, Line, XAxis, YAxis, Tooltip, ReferenceLine, ReferenceArea, ResponsiveContainer, CartesianGrid, type TooltipContentProps } from 'recharts'
import type { GameDetail, WinProbPlay } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl, teamPrimaryColor } from '../../utils/teams'
import { formatGameClock } from './formatting'

function colorRgb(hex: string) {
  const value = hex.replace('#', '')
  return [0, 2, 4].map(i => parseInt(value.slice(i, i + 2), 16))
}

function readableTeamColor(team: string) {
  const primary = teamPrimaryColor(team)
  const rgb = colorRgb(primary)
  const luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
  if (luminance >= 0.32) return primary
  const mixed = rgb.map(value => Math.round(value * 0.68 + 255 * 0.32))
  return `#${mixed.map(value => value.toString(16).padStart(2, '0')).join('')}`
}

function teamChartColors(awayTeam: string, homeTeam: string) {
  const home = readableTeamColor(homeTeam)
  const awayPrimary = readableTeamColor(awayTeam)
  const awayRgb = colorRgb(awayPrimary)
  const homeRgb = colorRgb(home)
  const distance = Math.sqrt(awayRgb.reduce((sum, value, i) => sum + (value - homeRgb[i]) ** 2, 0))
  return { away: distance < 90 ? '#f4f3f8' : awayPrimary, home }
}

function WpTooltip({ active, payload, awayColor, homeColor }: Pick<TooltipContentProps<number, string>, 'active' | 'payload'> & { awayColor: string; homeColor: string }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as ChartPoint
  return (
    <div className="bg-surface-card border border-surface-line rounded-xl px-3 py-2.5 shadow-2xl max-w-[220px] pointer-events-none">
      <div className="flex justify-between gap-3 text-xs font-bold mb-1.5">
        <span style={{ color: awayColor }}>{d.awayTeam} {(100 - d.wp).toFixed(1)}%</span>
        <span className="text-ink-dim font-normal">{formatGameClock(d.rem)}</span>
        <span style={{ color: homeColor }}>{d.homeTeam} {d.wp.toFixed(1)}%</span>
      </div>
      {d.desc && <p className="text-[11px] text-ink-dim leading-snug line-clamp-2">{d.desc}</p>}
    </div>
  )
}

interface ChartPoint {
  t: number; wp: number; awayWp: number; rem: number; desc: string | null
  td: boolean; turnover: boolean; posteam: string | null
  homeTeam: string; awayTeam: string
}

export function WinProbabilityChart({ game }: { game: GameDetail }) {
  const plays = game.win_prob
  if (!plays?.length) return null

  const homeTeam = game.home_team
  const awayTeam = game.away_team
  const colors = teamChartColors(awayTeam, homeTeam)

  const data: ChartPoint[] = plays.map((p: WinProbPlay) => ({
    t: 3600 - p.game_seconds_remaining,
    wp: Math.round(p.home_wp * 1000) / 10,
    awayWp: 100 - Math.round(p.home_wp * 1000) / 10,
    rem: p.game_seconds_remaining,
    desc: p.desc,
    td: p.touchdown === 1,
    turnover: p.interception === 1 || p.fumble_lost === 1,
    posteam: p.posteam,
    homeTeam,
    awayTeam,
  }))

  const maxT = Math.max(3600, data[data.length - 1]?.t ?? 3600)
  const finalWp = data[data.length - 1]?.wp ?? 50
  const scoringPlays = data.filter(d => d.td)
  const turnovers = data.filter(d => d.turnover)

  return (
    <Card title="Win Probability" action={<div className="flex items-center gap-4 text-xs text-ink-dim">
          <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: colors.away }} />{awayTeam}</span>
          <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: colors.home }} />{homeTeam}</span>
        </div>} className="mb-4">

      <div className="px-1 pt-3 pb-1">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="wpFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colors.home} stopOpacity={0.18} />
                <stop offset="100%" stopColor={colors.home} stopOpacity={0.02} />
              </linearGradient>
            </defs>

            <CartesianGrid vertical={false} stroke="#2e2b3e" strokeDasharray="0" />

            {/* Background territory tint */}
            <ReferenceArea y1={50} y2={100} fill={colors.home} fillOpacity={0.04} ifOverflow="hidden" />
            <ReferenceArea y1={0} y2={50} fill={colors.away} fillOpacity={0.04} ifOverflow="hidden" />

            {/* 50% line */}
            <ReferenceLine y={50} stroke="#2e2b3e" strokeDasharray="4 3" strokeWidth={1} />

            {/* Quarter separators */}
            {[900, 1800, 2700, 3600].filter(t => t < maxT).map(t => (
              <ReferenceLine key={t} x={t} stroke="#2e2b3e" strokeWidth={1.5} />
            ))}

            {/* Scoring play markers */}
            {scoringPlays.map((d, i) => (
              <ReferenceLine key={`td-${i}`} x={d.t} strokeWidth={1.5} strokeOpacity={0.55}
                stroke={d.posteam === homeTeam ? colors.home : colors.away} />
            ))}
            {turnovers.map((d, i) => (
              <ReferenceLine key={`to-${i}`} x={d.t} strokeWidth={1} strokeOpacity={0.4}
                stroke={d.posteam === homeTeam ? colors.away : colors.home} strokeDasharray="2 2" />
            ))}

            <XAxis dataKey="t" type="number" domain={[0, maxT]}
              ticks={[450, 1350, 2250, 3150, ...(maxT > 3600 ? [3825] : [])]}
              tickFormatter={v => (({ 450: 'Q1', 1350: 'Q2', 2250: 'Q3', 3150: 'Q4', 3825: 'OT' } as Record<number, string>)[v] ?? '')}
              tick={{ fill: '#6c6885', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} ticks={[0, 50, 100]}
              tickFormatter={v => v === 50 ? '50%' : `${v}%`}
              tick={{ fill: '#2e2b3e', fontSize: 10 }} axisLine={false} tickLine={false} width={34} />

            <Tooltip content={props => <WpTooltip {...props} awayColor={colors.away} homeColor={colors.home} />} cursor={{ stroke: '#a3a0b8', strokeWidth: 1, strokeDasharray: '3 3' }} />

            <Area type="monotone" dataKey="wp" stroke={colors.home} strokeWidth={2.5}
              fill="url(#wpFill)" dot={false}
              activeDot={{ r: 5, fill: colors.home, stroke: '#0e0d15', strokeWidth: 2 }} />
            <Line type="monotone" dataKey="awayWp" stroke={colors.away} strokeWidth={2} dot={false}
              activeDot={{ r: 4, fill: colors.away, stroke: '#0e0d15', strokeWidth: 2 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Footer */}
      <div className="px-5 pb-4 pt-1 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img src={teamLogoUrl(awayTeam)} className="w-6 h-6 object-contain opacity-60" alt="" />
          <span className="text-lg font-black tabular-nums" style={{ color: colors.away }}>{(100 - finalWp).toFixed(0)}%</span>
        </div>
        <span className="text-[10px] text-ink-dim uppercase tracking-widest">final</span>
        <div className="flex items-center gap-2">
          <span className="text-lg font-black tabular-nums" style={{ color: colors.home }}>{finalWp.toFixed(0)}%</span>
          <img src={teamLogoUrl(homeTeam)} className="w-6 h-6 object-contain opacity-60" alt="" />
        </div>
      </div>
    </Card>
  )
}
