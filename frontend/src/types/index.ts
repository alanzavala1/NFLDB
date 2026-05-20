/**
 * Friendly aliases for backend Pydantic models.
 *
 * Source of truth: api/schemas/*.py -> generated into ./api.d.ts via
 * `npm run gen-types`. Do not hand-edit api.d.ts.
 *
 * Add new aliases here as more endpoints get Pydantic response_models.
 */
import type { components } from './api'

type Schemas = components['schemas']

export type HealthResponse    = Schemas['HealthResponse']
export type SeasonStatus      = Schemas['SeasonStatus']
export type LoadSeasonResponse = Schemas['LoadSeasonResponse']
export type RosterPlayer      = Schemas['RosterPlayer']
export type StandingsRow      = Schemas['StandingsRow']
export type DivisionStandings = Schemas['DivisionStandings']
