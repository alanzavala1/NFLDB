import type { ReactNode } from 'react'
import type { PlayerSplit, TeamSplit, DefensiveSplit } from '../../types'

// ── Metric spec ──────────────────────────────────────────────────────────────

export type Metric<R> = {
  key: string
  label: string
  value: (r: R) => number | null      // numeric — for ranking / best-in-row
  fmt: (v: number) => string          // display string
  higherIsBetter?: boolean            // undefined ⇒ neutral (no winner shading)
  group?: string                      // section header in the Compare view
}

export type Dim = { key: string; label: string }

export type PlayerCategory = 'passing' | 'rushing' | 'receiving'

export type TeamSide = 'offense' | 'defense'

// ── Quick situational presets (the prominent filter chips) ───────────────────

export type Situation = { label: string; dim: string; value: string }

export type ComparisonMode = 'players' | 'teams'

export type PlayerLens = PlayerCategory | 'defense'

export type PlayerEntity = { id: string; name: string; headshot?: string | null; sub?: string }

export type SplitRow = PlayerSplit | TeamSplit | DefensiveSplit

export type EntityCard = { key: string; label: string; sub?: string; headshot?: string | null; logo?: string; color: string }

export type TableSort = { key: string; dir: 'asc' | 'desc' }

export type SplitTableRow = { key: string; label: ReactNode; row: SplitRow | null; defRk?: number | null; sub?: boolean }

// One-click starters for the empty state — resolved through search so no
// player ids are hardcoded.
export type Example = { label: string; names?: string[]; cat?: PlayerLens; teams?: string[] }

export type GameRecordLite = { game_id: string; season: number; week: number; location: string; opponent: string }

export type GroupedSectionData = { map: Map<string, SplitRow>; total: SplitRow | null; groups?: Map<string, { g: GameRecordLite; r: SplitRow }[]> }

export interface ComparisonSelection {
  mode: ComparisonMode
  playerLens: PlayerLens
  teamSide: TeamSide
  players: PlayerEntity[]
  teams: string[]
  season: number | null // null means availability is pending, empty, or invalid.
  situation: Situation | null
}
