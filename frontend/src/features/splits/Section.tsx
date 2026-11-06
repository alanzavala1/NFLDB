import type { ReactNode } from 'react'

export function Section({ title, children, open, onToggle }: { title: string; children: ReactNode; open: boolean; onToggle: () => void }) {
  return (
    <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">
      <button aria-expanded={open} onClick={onToggle} className="min-h-11 w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-raise/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-indigo-400">
        <span className="text-xs font-bold text-ink-mid uppercase tracking-wider">{title}</span>
        <span className="text-ink-dim text-xs">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="border-t border-surface-line">{children}</div>}
    </div>
  )
}
