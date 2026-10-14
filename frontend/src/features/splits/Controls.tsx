import type { ReactNode } from 'react'

export function SegmentControl<T extends string | number>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex items-center gap-0.5 bg-surface-card border border-surface-line rounded-lg p-0.5 flex-wrap">
      {options.map(o => (
        <button key={String(o.value)} onClick={() => onChange(o.value)}
          className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${value === o.value ? 'bg-indigo-600 text-ink' : 'text-ink-mid hover:text-ink'}`}>{o.label}</button>
      ))}
    </div>
  )
}

export function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors ${active ? 'bg-indigo-600 border-indigo-500 text-ink' : 'bg-surface-card border-surface-line text-ink-mid hover:text-ink hover:border-surface-line'}`}>{children}</button>
  )
}
