import { hasUnavailableReceivingField, hasUnavailableTargets, type ReceivingStats } from '../utils/receiving'

/** An expected source gap is informational; it does not make the page an error. */
export default function ReceivingDataNote({ rows = [], unavailable = false, career = false }: {
  rows?: ReceivingStats[]; unavailable?: boolean; career?: boolean
}) {
  const targets = unavailable || hasUnavailableTargets(rows)
  const air = hasUnavailableReceivingField(rows, 'air_yards')
  const yac = hasUnavailableReceivingField(rows, 'yac')
  if (!targets && !air && !yac) return null
  return <aside aria-label="Receiving data availability" className="mb-4 rounded-lg border border-surface-line bg-surface-card px-4 py-3 text-sm text-ink-mid">
    <p className="font-semibold text-ink">Receiving data availability</p>
    {targets && <p className="mt-1">Targets and target-based rates are shown as — where target records are incomplete (2003–2008).</p>}
    {yac && <p className="mt-1">Yards after catch (YAC) and YAC per reception are shown as — before 2006.</p>}
    {air && <p className="mt-1">Receiving air yards and air-yard rates are shown as — before 2009.</p>}
    <p className="mt-1">Receptions, receiving yards and touchdowns are still shown.</p>
    {career && <p className="mt-1 text-ink-dim">Career totals and rates for an affected statistic are unavailable when any included season is affected.</p>}
  </aside>
}
