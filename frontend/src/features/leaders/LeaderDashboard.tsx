import type { LeagueLeader } from '../../types'
import { teamLogoUrl } from '../../utils/teams'
import { STAT_PRIMARY, type PrimaryStat } from './primaryStats'

interface DashboardCategory {
  key: string
  label: string
  tabKey: string
  filter: (p: LeagueLeader) => boolean
  primary: PrimaryStat
}

const DASHBOARD_CATEGORIES: DashboardCategory[] = [
  { key: 'pass_yds', label: 'Passing Leader',   tabKey: 'passing',   filter: p => p.attempts >= 100,                   primary: STAT_PRIMARY.passing },
  { key: 'rush_yds', label: 'Rushing Leader',   tabKey: 'rushing',   filter: p => p.carries >= 50,                     primary: STAT_PRIMARY.rushing },
  { key: 'rec_yds',  label: 'Receiving Leader', tabKey: 'receiving', filter: p => p.targets >= 20,                     primary: STAT_PRIMARY.receiving },
  { key: 'tkl',      label: 'Tackles Leader',   tabKey: 'defense',   filter: p => p.solo_tackles + p.assist_tackles >= 10, primary: STAT_PRIMARY.defense },
]

function DashboardTile({ cat, leaders, onClick }: { cat: DashboardCategory; leaders: LeagueLeader[]; onClick: () => void }) {
  const top = leaders.filter(cat.filter).sort((a, b) => cat.primary.value(b) - cat.primary.value(a))[0]
  if (!top) {
    return (
      <button onClick={onClick} className="bg-surface-card border border-surface-line rounded-xl p-4 text-left hover:border-surface-line transition-colors min-h-[148px]">
        <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest">{cat.label}</div>
        <p className="text-xs text-ink-dim mt-4">No data yet</p>
      </button>
    )
  }
  return (
    <button onClick={onClick} className="bg-surface-card border border-surface-line rounded-xl p-4 text-left hover:border-indigo-600 hover:bg-surface-card/70 transition-all w-full">
      <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest mb-3">{cat.label}</div>
      <div className="flex items-center gap-3">
        {top.headshot_url
          ? <img src={top.headshot_url} className="w-12 h-12 rounded-full object-cover object-top shrink-0 bg-surface-raise" alt="" />
          : <div className="w-12 h-12 rounded-full bg-surface-raise shrink-0" />
        }
        <div className="flex-1 min-w-0">
          <div className="text-sm font-bold text-ink truncate">{top.player_name}</div>
          <div className="text-[11px] text-ink-dim flex items-center gap-1.5 mt-0.5">
            {top.team && <img src={teamLogoUrl(top.team)} className="w-3.5 h-3.5 object-contain opacity-80" alt="" />}
            <span>{top.team ?? '—'}</span>
            {top.position && <><span className="text-ink-dim">·</span><span>{top.position}</span></>}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-baseline justify-between">
        <span className="text-2xl font-black text-ink tabular-nums leading-none">{cat.primary.display(top)}</span>
        <span className="text-[10px] font-bold uppercase tracking-widest text-ink-dim">{cat.primary.label}</span>
      </div>
      <div className="text-[11px] text-ink-dim mt-1.5 truncate">{cat.primary.secondary(top)}</div>
    </button>
  )
}

export function StatDashboard({ leaders, onPick }: { leaders: LeagueLeader[]; onPick: (tabKey: string) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
      {DASHBOARD_CATEGORIES.map(c => (
        <DashboardTile key={c.key} cat={c} leaders={leaders} onClick={() => onPick(c.tabKey)} />
      ))}
    </div>
  )
}
