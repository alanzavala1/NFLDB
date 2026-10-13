// Navigation context is browser route state, separate from API responses.
export interface GameOrigin {
  gameId: string
  season: number
  week: number
  awayTeam: string
  homeTeam: string
  fromWeek?: number
}

export interface PlayerLocationState {
  fromGame?: GameOrigin
}
