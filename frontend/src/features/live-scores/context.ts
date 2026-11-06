import { createContext } from 'react'
import type { LiveGameOut } from '../../types'

export const EMPTY_GAMES: Record<string, LiveGameOut> = {}
export const LiveScoresContext = createContext(EMPTY_GAMES)
