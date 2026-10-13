import { useQuery } from '@tanstack/react-query'
import type { WpaLeaders } from '../../types'
import { wpaLeadersQueryOptions } from '../../api/wpaLeaders'
import Card from '../../components/Card'
import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import { WpaTable } from './WpaTable'

export type WpaSubTab = keyof WpaLeaders

export function WpaPanel({ season, subTab, onSubTabChange }: {
  season: number
  subTab: WpaSubTab
  onSubTabChange: (tab: WpaSubTab) => void
}) {
  const query = useQuery(wpaLeadersQueryOptions(season))
  const players = query.data?.[subTab] ?? []
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex gap-1 bg-surface-card border border-surface-line rounded-xl p-1 w-fit">
          {(['passing', 'rushing', 'receiving'] as const).map(tab => (
            <button key={tab} onClick={() => onSubTabChange(tab)} aria-pressed={subTab === tab}
              className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-colors ${subTab === tab ? 'bg-indigo-600 text-ink' : 'text-ink-mid hover:text-ink'}`}>
              {tab}
            </button>
          ))}
        </div>
        <span className="text-xs text-ink-dim">
          {subTab === 'passing' ? 'Air WPA credited to passer (≥50 att)' : subTab === 'rushing' ? 'WPA on rush plays (≥50 car)' : 'YAC WPA credited to receiver (≥20 rec)'}
        </span>
      </div>
      <Card title="WPA leaders">
        {(query.error || query.isPending || !players.length) && <div className="p-4">
          <QueryFailure resource="WPA leaders" error={query.error} hasData={query.data !== undefined} onRetry={() => void query.refetch()} />
          {query.isPending && <QueryLoading>Loading WPA leaders…</QueryLoading>}
          {!query.isPending && query.data !== undefined && !players.length && <p className="text-ink-dim text-sm">No WPA data for {season}.</p>}
        </div>}
        {players.length > 0 && <WpaTable players={players} contextLabel={subTab === 'passing' ? 'ATT' : subTab === 'rushing' ? 'CAR' : 'REC'} />}
      </Card>
    </div>
  )
}
