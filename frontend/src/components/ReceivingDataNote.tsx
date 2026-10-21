/** An expected source gap is informational; it does not make the page an error. */
export default function ReceivingDataNote({ unavailable, career = false }: { unavailable: boolean; career?: boolean }) {
  if (!unavailable) return null
  return <aside aria-label="Receiving data availability" className="mb-4 rounded-lg border border-surface-line bg-surface-card px-4 py-3 text-sm text-ink-mid">
    <p className="font-semibold text-ink">Targets unavailable</p>
    <p className="mt-1">The source has incomplete target data for {career ? 'some seasons in this career' : 'this view'}. Targets and rates based on them are shown as —. Receptions, receiving yards and touchdowns are still shown.</p>
    {career && <p className="mt-1 text-ink-dim">Career target totals and rates are unavailable when any included season is affected.</p>}
  </aside>
}
