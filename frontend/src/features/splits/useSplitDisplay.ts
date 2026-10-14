import { useState } from 'react'

export function useSplitDisplay(defaultOpen: string[]) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [keyStatsOnly, setKeyStatsOnly] = useState(true)
  const isOpen = (k: string) => openSections.has(k) || (!openSections.has(`!${k}`) && defaultOpen.includes(k))
  const toggleOpen = (k: string) => setOpenSections(s => { const n = new Set(s); const open = isOpen(k); n.delete(k); n.delete(`!${k}`); n.add(open ? `!${k}` : k); return n })
  function toggleHidden(key: string) {
    setHidden(previous => { const next = new Set(previous); if (next.has(key)) next.delete(key); else next.add(key); return next })
  }
  function toggleExpanded(key: string) {
    setExpandedKeys(previous => { const next = new Set(previous); if (next.has(key)) next.delete(key); else next.add(key); return next })
  }
  return { hidden, expandedKeys, keyStatsOnly, setKeyStatsOnly, isOpen, toggleOpen, toggleHidden, toggleExpanded }
}
