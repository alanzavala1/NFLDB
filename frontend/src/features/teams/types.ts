import type { TeamLeader, TeamSplit } from '../../types'
import type { SortingState } from '@tanstack/react-table'

type ColKind = 'trad' | 'adv'

export type SectionKind = 'passing' | 'rushing' | 'receiving' | 'scrimmage' | 'defense'
export type SectionSorting = Record<SectionKind, SortingState>

export type TCol = {
  key: string; label: string; kind: ColKind
  sortVal: (p: TeamLeader) => number
  render: (p: TeamLeader, totals: SectionTotals) => string | number | null
  highlight?: boolean; dim?: boolean
  share?: (p: TeamLeader, totals: SectionTotals) => number
  total?: (totals: SectionTotals, games: number) => string | number | null
}

export type SectionTotals = {
  attempts: number; completions: number; pass_yards: number; pass_tds: number
  interceptions_thrown: number; sacks_taken: number; pass_epa: number
  carries: number; rush_yards: number; rush_tds: number; rush_epa: number
  targets: number; receptions: number; rec_yards: number; rec_tds: number
  air_yards: number; yac: number; rec_epa: number
  solo_tackles: number; assist_tackles: number; sacks: number; tackles_for_loss: number
  qb_hits: number; def_interceptions: number; pass_breakups: number
  forced_fumbles: number; fumble_recoveries: number
}

export type SummaryBox = { label: string; value: string; hint?: string }

export type MetricSpec = {
  key: string
  label: string
  hint?: string
  value: number | null | undefined
  rank: number | null | undefined
  fmt: (v: number) => string
}

export type TeamSplitCol = { label: string; get: (r: TeamSplit) => string | null; signed?: boolean; highlight?: boolean; heat?: 'epa' | 'pct' }
