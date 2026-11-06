import type { TeamProfile } from '../../types'
import { weekLabel } from './selectors'
import { ResponsiveContainer, BarChart, XAxis, ReferenceLine, Tooltip, Bar, Cell } from 'recharts'

export default function ScoreChart({ profile }: { profile: TeamProfile }) {
  const data = profile.games
    .filter(g => (g.away_team === profile.team ? g.away_score : g.home_score) !== null)
    .map(g => {
      const isAway = g.away_team === profile.team
      const pf = (isAway ? g.away_score : g.home_score) ?? 0
      const pa = (isAway ? g.home_score : g.away_score) ?? 0
      return { name: weekLabel(g.week, g.game_type), diff: pf - pa, pf, pa }
    })

  if (data.length === 0) return null

  return (
    <div className="bg-surface-card border border-surface-line rounded-xl px-4 pt-4 pb-2 mb-4">
      <div className="text-xs font-bold text-ink-dim uppercase tracking-wider mb-3">Point Differential</div>
      <ResponsiveContainer width="100%" height={90}>
        <BarChart data={data} barSize={14} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#6c6885' }} axisLine={false} tickLine={false} interval={0} />
          <ReferenceLine y={0} stroke="#2e2b3e" strokeWidth={1} />
          <Tooltip
            contentStyle={{ background: '#1b1a26', border: '1px solid #2e2b3e', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: '#a3a0b8' }}
            formatter={(_v, _n, entry) => {
              const { pf, pa, diff } = entry.payload
              return [`${pf}–${pa}  (${diff >= 0 ? '+' : ''}${diff})`, 'Score']
            }}
          />
          <Bar dataKey="diff" radius={[2, 2, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.diff >= 0 ? '#34d399' : '#f87171'} fillOpacity={0.75} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
