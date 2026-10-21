import ReceivingDataNote from '../../components/ReceivingDataNote'
import { hasUnavailableTargets } from '../../utils/receiving'
import type { TeamProfile } from '../../types'
import { useState } from 'react'
import { computeRecord } from './selectors'
import FullStatsModal from './FullStatsModal'
import RosterModal from './RosterModal'
import SeasonSummary from './SeasonSummary'
import TeamAnalytics from './TeamAnalytics'
import TeamSplitsPanel from './TeamSplitsPanel'
import InjuryReportPanel from './InjuryReportPanel'
import StartingLineupPanel from './StartingLineupPanel'
import ScoreChart from './ScoreChart'
import SchedulePanel from './SchedulePanel'
import LeadersPanel from './LeadersPanel'

export default function SeasonDetail({ profile }: { profile: TeamProfile }) {
  const [statsOpen, setStatsOpen] = useState(false)
  const [rosterOpen, setRosterOpen] = useState(false)
  const { w, l, t, label } = computeRecord(profile.games, profile.team)
  const played = w + l + t

  return (
    <>
      {statsOpen && <FullStatsModal profile={profile} onClose={() => setStatsOpen(false)} />}
      {rosterOpen && <RosterModal profile={profile} onClose={() => setRosterOpen(false)} />}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-ink font-bold text-xl">{profile.season} Season</div>
          <div className="text-ink-dim text-sm">{played} games · {label}</div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setRosterOpen(true)}
            className="text-sm text-ink-mid hover:text-ink bg-surface-raise/60 hover:bg-surface-raise/60 border border-surface-line rounded-lg px-4 py-2 transition-colors font-medium"
          >
            Roster
          </button>
          <button
            onClick={() => setStatsOpen(true)}
            className="text-sm text-indigo-400 hover:text-ink bg-indigo-900/30 hover:bg-indigo-800/50 border border-indigo-700/50 rounded-lg px-4 py-2 transition-colors font-medium"
          >
            Full Stats
          </button>
        </div>
      </div>
      <ReceivingDataNote unavailable={hasUnavailableTargets([...profile.leaders, ...profile.playoff_leaders])} />
      <SeasonSummary profile={profile} />
      <TeamAnalytics team={profile.team} season={profile.season} />
      <TeamSplitsPanel team={profile.team} season={profile.season} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <InjuryReportPanel team={profile.team} season={profile.season} />
        <StartingLineupPanel team={profile.team} season={profile.season} />
      </div>
      <ScoreChart profile={profile} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden flex flex-col">
          <div className="px-4 py-2.5 border-b border-surface-line">
            <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">Schedule</span>
          </div>
          <SchedulePanel profile={profile} />
        </div>
        <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden flex flex-col">
          <div className="px-4 py-2.5 border-b border-surface-line">
            <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">Leaders</span>
          </div>
          <LeadersPanel leaders={profile.leaders} onViewFull={() => setStatsOpen(true)} />
        </div>
      </div>
    </>
  )
}
